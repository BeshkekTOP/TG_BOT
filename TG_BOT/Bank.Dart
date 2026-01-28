void main() {
  final account = BankAccount(
    accountNumber: 'ACC123456789',
    initialBalance: 1000.0,
  );

  print('=== Банковский счёт ===');
  print('Номер счёта: ${account.accountNumber}');
  print('Текущий баланс: \$${account.balance}\n');

  try {
    account.deposit(500.0);
    print('Пополнение на \$500 успешно.');
    print('Новый баланс: \$${account.balance}\n');
  } catch (e) {
    print('Ошибка при пополнении: $e\n');
  }

  bool success = account.withdraw(200.0);
  if (success) {
    print('Снятие \$200 успешно.');
    print('Новый баланс: \$${account.balance}\n');
  } else {
    print('Недостаточно средств для снятия \$200.\n');
  }

  success = account.withdraw(2000.0);
  if (success) {
    print('Снятие \$2000 успешно.');
  } else {
    print('Недостаточно средств для снятия \$2000.');
    print('Баланс остаётся: \$${account.balance}\n');
  }

  try {
    account.deposit(-100.0);
  } catch (e) {
    print('Попытка пополнить отрицательной суммой: $e\n');
  }

  final badAccount = BankAccount(
    accountNumber: 'ACC987654321',
    initialBalance: -500.0, 
  );
  print('Счёт с отрицательным начальным балансом:');
  print('Номер: ${badAccount.accountNumber}');
  print('Баланс (исправлен на 0): \$${badAccount.balance}');
}

class BankAccount {
  final String _accountNumber;
  double _balance;

  BankAccount({
    required String accountNumber,
    required double initialBalance,
  })  : _accountNumber = accountNumber,
        _balance = initialBalance >= 0 ? initialBalance : 0;

  String get accountNumber => _accountNumber;

  double get balance => _balance;

  void deposit(double amount) {
    if (amount <= 0) {
      throw ArgumentError('Сумма пополнения должна быть положительной');
    }
    _balance += amount;
  }

  bool withdraw(double amount) {
    if (amount <= 0) {
      throw ArgumentError('Сумма снятия должна быть положительной');
    }
    if (amount > _balance) {
      return false; 
    }
    _balance -= amount;
    return true; 
  }
}